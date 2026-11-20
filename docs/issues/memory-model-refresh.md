# subscription usage and the 6.2 model candidate

[adr 0093](../decisions/0093-subscription-model-refresh.md) owns the role
selection and isolated release qualification. the blinded comparison selected
`gpt-6.1-terra/medium` for compaction. the installed quota effect remains open.

production release `e7f5916` ran `gpt-6-astra/max` for main and
`gpt-6.1-sol/xhigh` for both memory roles through personal codex. its contained
stock `0.160.0` catalog lacks the 6.2 models. the personal pro account listed
`gpt-6.2-astra` and `gpt-6.2-sol` on mac stock `0.171.0` on 2026-11-20.
openai requires at least `0.166.0` for these models. embeddings use the
separate api-backed `text-embedding-3-small` route. [codex requirements](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)

from process start at 06:31:26 through 15:07 utc on november 20, the service
journal, native attempt receipts and contained stock metadata showed the
following usage. cached input is included in input. reasoning is included in
output.

| role | activity | reported input | reported output |
| --- | --- | ---: | ---: |
| compactor | 163 completed runs, 1,304 inferred nodes. 19 more runs lacked usage | 2,036,426, cache breakdown unknown | 1,217,047 |
| main | 18 successful root attempts. one failed attempt lacked usage | 3,042,656, including 2,091,392 cached | 15,266, including 10,110 reasoning |
| dreamer | one nightly attempt, five native turns, ended in `MemoryError` without advancing | unknown | unknown |

at published standard purchased-credit rates, the reported tokens alone give
about 309 credits for main and 309–406 for compaction, depending on its cache
fraction. each sol version has the same per-token rate. the personal meter
showed 12% of the shared weekly allowance used at about 15:10 utc. the meter
provides no per-role attribution. the compactor [parked on a native event
burst](compactor-native-event-buffer.md) before the predeclared busy interval.
[codex rates](https://learn.chatgpt.com/docs/pricing#token-rates)

two native `gpt-6.2-sol` children ran the installed compactor instructions on
the same synthetic eight-address batch. both preserved the corrected booking,
conflicting counts, receipt identities, ambiguous assent, withdrawn inference
and source boundaries. all nodes fit 512 bytes. the summarizing step reported
668 output tokens at `medium` and 897 at `xhigh`, including 48 and 160
reasoning tokens respectively. each read the same fixture once. this checks one
batch on the mac client. the fixture sha-256 was
`1bde7b40ac9d7ec694aa033621cea15f451b9a5c8f8ae11b3246ee74ecbccb4d`.
ordinary production throughput, quota savings and multi-level recall still
need evidence.

three paired, blinded trials started from the same five redacted real excerpts
and three synthetic cases. each run committed two inferred leaves, two inferred
parents and eleven free nodes. terra/medium, sol/medium and the incumbent
sol/xhigh preserved every required fact and reopened the correction and tool
result through their own ancestry. both luna efforts assigned a receipt to the
wrong sibling during screening.

terra/medium averaged 0.071567 standard-credit equivalents per committed
inferred node. sol/medium averaged 0.152392 and the incumbent 0.327575.
terra cost less per node and per complete tree in every pair. six of its
twelve inferred nodes exceeded the 512-byte target. the largest used 772 of
the 2,048 permitted bytes. the dated report, anonymous grades, usage and
packet remain in the owner's private qualification directory under
`adr0093-implementation-20261120/evaluation/compactor-comparison.md`,
sha-256 `58b09b51ea35b871fe3cc3209e0e3aa4064b85cb67de15a3c6ee3282fdc4e2ab`.

the scheduler can spend saved capacity on older history. a separately
authorized installed observation measures the fixed-cutoff deficit, later
arrivals and source-backed recall. keep the earlier production window under
its original pins. [capacity and recall](../compactor-burst-recovery.md#installed-recovery-and-user-outcome)

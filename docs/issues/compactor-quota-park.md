# compactor parks when subscription quota is exhausted

the kernel can report `quota_exhausted` without a usable model result.
the writer records the existing `invalid_completion` park and logs the exact
stop kind. later quota availability alone leaves the historical prefix parked.
capture and reads have separate ownership.

on november 25 at 06:48:37 utc, `74bfcab/0023` compactor v8 logged
`quota_exhausted` in run `2d69ac2e-dcb9-4f70-a35f-7ba561860253`. the batch's
only inference call had two fields, no retry, and no reported token counts.
it left the entire batch uncommitted and recorded `invalid_completion` at
generation 2 address `28456+1`. the node was still absent at 17:00 utc.
both services remained active. archive admission continued. the frozen
busy cutoff was already complete. 346 later positions and 697 nodes were
outstanding at quiet end, after 10h11m22s with the mark. the stop journal
does not establish the exact quota bucket or when allowance returned.
[capacity evidence](memory-usefulness-evaluation.md#installed-terra-observation)

the mac retains `window/park-28456-1.journal.jsonl`, sha-256
`8c783eebef8d724814f87e5e31b4b98b66abbc10725049d4760afab15ce1bcf0`, and
`window/park-28456-1.snapshot.json`, sha-256
`b36cc7ff80e280648bc90d5b25718bc6049f15f2725de20813250daab9ba32ce`.

during [capacity observation](../operations.md#chronological-capacity-observation),
classify the cause from the stop journal before calling a park a malformed
result. measure any actual quota exits and the cost of their stopped interval.
resolve once that evidence warrants a recovery change and an installed check
proves capture, writer ownership and finite submission bounds through it.

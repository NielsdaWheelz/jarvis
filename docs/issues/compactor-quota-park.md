# compactor parks when subscription quota is exhausted

the kernel can report `quota_exhausted` without a usable model result.
the writer records the existing `invalid_completion` park and logs the exact
stop kind. later quota availability alone leaves the historical prefix parked.
capture and reads have separate ownership.

during [capacity observation](../operations.md#chronological-capacity-observation),
classify the cause from the stop journal before calling a park a malformed
result. measure any actual quota exits and the cost of their stopped interval.
resolve once that evidence warrants a recovery change and an installed check
proves capture, writer ownership and finite submission bounds through it.

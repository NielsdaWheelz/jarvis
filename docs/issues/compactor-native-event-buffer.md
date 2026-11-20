# historical compaction parked on a native event burst

[adr 0093](../decisions/0093-subscription-model-refresh.md) owns the candidate
burst checks. installed range recovery requires a later authorized cut.

on 2026-11-20 at 14:16:34 utc, production release `e7f5916` parked compaction
at `8112+8`. run `3fd97c10-6e07-421a-bc23-f701adfbc1b5` had eight tasks,
one provider turn and 154.169 seconds elapsed. both token counters were absent.
at 15:13 utc the same park persisted. the ready prefix ended at 8,184 of
50,435 admitted positions. this affects the [historical capacity observation](memory-usefulness-evaluation.md).

the `jarvis.service` journal recorded `protocol_defect` in provider `f42d6cf`,
`codex_sdk.py`, `_read` line 2679 → `_publish` line 2744. that branch fires
when either the pending event count or the aggregate queued bytes exceeds its
bound. the trace does not distinguish those conditions. jarvis recorded
`configuration_error` and persisted `invalid_completion` at the node. the
contained stock logs showed an active stream. the account charge is unknown.
[provider source](https://github.com/NielsdaWheelz/llm-calling/blob/f42d6cf/src/provider_runtime/agent_runtime/codex_sdk.py#L2743)

inspect the original diagnostics with `journalctl -u jarvis.service --since
'2026-11-20 14:16:30 UTC' --until '2026-11-20 14:16:38 UTC'` on dev-server.
resolve when both predecessor limits have independent reproductions, the
candidate drains the qualifying burst in order, and installed readback proves
the parked parent completed and later historical construction advanced. the
historical trigger remains unknown unless further incident evidence identifies
it. [implementation and acceptance](../compactor-burst-recovery.md)

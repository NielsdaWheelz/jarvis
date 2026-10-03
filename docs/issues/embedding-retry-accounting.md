# embedding retry accounting

problem: memory search reserves/reports one external attempt, but its shared
embedding runtime uses the provider library's default of up to three attempts.

impact: a transient embedding failure can cause additional provider requests
without matching tool-attempt accounting. this is an existing code/contract
discrepancy, not merely an unimplemented universal-memory feature.

evidence (2026-10-01): `src/jarvis/embeddings.py` constructs `ProviderRuntime`
without `retry`; pinned provider-runtime `runtime.py` defaults that parameter to
`DEFAULT_RETRY`, and `retry.py` sets `max_attempts=3`. its `embed` uses that policy.
`src/jarvis/memory_tools.py` sets `actual_attempts=1` for embedding search and the
binding allows one external attempt. code inspection only; no failure injected.

resolution: set an explicit public `RetryPolicy(max_attempts=1, ...)` on the one
shared embedding runtime. use it for search and indexing; later background sweeps
retry indexing. retain typed search failure and truthful attempt accounting under
the universal-memory target. disabling sdk retry alone does not change the
provider-runtime retry loop. no separate client or retry framework.

resolved when: transient failure produces at most one provider request for an
invocation, all consumers share the configured runtime, and search's recorded
attempt count matches observed requests. implement the focused check under the
memory verification slice; no behavioral check or runtime fix is claimed here.

# universal memory native capture

problem: the [universal memory contract](../universal-memory.md) needs
provider-runtime archive codecs that enumerate and read every configured native
home without resuming, give stable never-reused event identities, mark jarvis's
own cognition sessions before they persist, and recognize jarvis memory-tool
results. `memory_save_note` call arguments and results/errors must also become content-free
references, even after failed saves or missing receipts; otherwise retrieved or
submitted prose can re-enter extraction as new evidence. none of this exists yet.

the current [capture contract](../universal-memory.md#3-native-capture), simplified
by [adr 0062](../decisions/0062-simplify-memory-policy-and-retrieval.md), accepts
complete normalized events atomically; the central service then stores 8,000-byte
chunks. oversized events park capture until repaired, without truncation or skip.
changed history, conflicting identity or a lost activation boundary also parks
and reports the conversation; there is no automatic checkpoint reset or replay.
an admitted collector activates the lane online after a complete inventory, with
receipt and per-conversation baselines in one transaction. no temporary inventory
file, manual activation or jarvis stop is required; an incomplete inventory may
need a quiet native lane. validate mapped native fields strictly and ignore
unrelated additive fields; this does not relax closed model or api schemas.

impact: no native lane can activate until its archive capabilities are qualified
on the installed provider. this is not a native-version allowlist.
the devbox codex-personal lane, which also hosts jarvis cognition, stays
unadmitted until internal marking is qualified, or cognition moves to sessions
that never persist (see [shared cognition](codex-private-process.md)).

evidence (2026-09-28):

- provider-runtime `sessions.py` session snapshots are metadata-only. codex
  `read_session` resumes the thread (`codex_sdk.py` `thread_resume`), and
  `list_sessions` omits archived, exec and subagent threads.
- the claude adapter refuses isolated-root discovery and history
  (`claude_sdk.py` `list_sessions`/`read_session`). the claude agent sdk's own
  reader follows one chain from the newest leaf and returns empty history for a
  missing session, so it cannot serve as the codec.
- in `.codex-work`, 1,039 of 1,313 threads are legacy or unmarked history mode,
  whose item and turn ids are synthesized at read time. rollouts reach 472 mb,
  over provider-runtime's 4 mib message cap. about 8–9% of codex turns have no
  terminal event, and claude has no native turn end.
- provider-runtime certifies codex 0.144.4 while the hosts run 0.157.1; codex's
  `threadSource` and paged item reads postdate the certified version.
- provider-runtime hard-codes its client name, so `originator` does not identify
  jarvis threads.

resolved when: codecs validate every mapped native field and demonstrate complete
activation inventory and read-only coverage, stable event identity, internal
marking, memory-tool echo suppression (including failed saves) and child-result
recognition on installed providers, including closed and archived conversations.
focused capture/retry checks prove automatic activation and complete-event
atomicity. harmless additive fields are ignored; oversized, changed or conflicting
history parks without advancing the checkpoint. confirm each admitted lane's
mapping and record the observed versions and results; do not build a recurring
fleet qualification matrix. no raw-transcript parsing outside provider-runtime,
screen capture, resumed-thread read or legacy-reader fallback.

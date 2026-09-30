# universal memory native capture

problem: the [universal memory contract](../universal-memory.md) needs
provider-runtime archive codecs that enumerate and read every configured native
home without resuming, give stable never-reused event identities, mark jarvis's
own cognition sessions before they persist, and recognize jarvis memory-tool
results. none of this exists yet.

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

resolved when: package a's schema-strict codecs pass the contract's coverage,
complete activation inventory, inclusive reread, identity, rewrite, branch, gap,
internal-marking, memory-tool and child-result
recognition journeys against the installed provider versions on every lane that
is to be admitted, including closed and archived conversations; a dated report
records exact revisions, provider versions and results. no raw-transcript parsing
outside provider-runtime, screen capture, resumed-thread read or legacy-reader
fallback.

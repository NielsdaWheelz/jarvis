# worker outcome recovery

problem: `ActionStore.unreported_terminal` can select an already reported
`agent.wait` again while an original input remains unprocessed, if its native
tool-result receipt was lost. recovery can repeatedly select the same work
before main gets to integrate the published event.

impact: a durable worker observation can starve its own continuation after a
registration-reply crash.

evidence: source `8c0bf36`, `src/jarvis/actions.py:914–1030`: report eligibility
includes an alternative based on original `processed_at`, despite an existing
resolution identity. read-only audit, 2026-11-14; no behavioral proof run.

reproduction: retain a committed wait registration/outcome and its canonical
resolution, omit the native tool-result reply, leave an original input unfinished,
then run real action recovery before main.

resolved when [slice 1](../one-main-events.md) uses absence of the exact canonical
outcome as report eligibility and counts only new publication as progress. prove
recovery terminates and main receives the existing observation without duplicate
publication. local consent receipts must not masquerade as delivered effect
receipts. delete this record after accepted temporary integration proof.

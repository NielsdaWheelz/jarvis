# macbook work2 pending baselines

status: two pending conversations observed during the 2026-11-15 online rollout;
healthy and new work2 capture is qualified.

problem: two codex-work2 conversations still report baseline_error=unavailable.
their native files exist; metadata/file-existence checks do not establish why a
stable head was unavailable. do not conflate this with dev-server's proven
missing original rollouts or infer a cause merely from recent activity.

impact: these recorded identities cannot ingest until a successful head read
establishes their first cut. automatic retries continue. the owner-approved
policy excludes activity before that eventual cut; other conversations proceed.

evidence: the installed lane and normal synthetic model→capture→mcp journey
pass. pending rows have no captured originals. diagnosis used metadata and file
existence only, without changing native files or treating an unreadable head as
empty. a present file is not proof of complete, stable, readable native lineage.

resolved when: each pending row obtains its one canonical stable cut through
normal collection, then later activity captures exactly once beyond it. preserve
old cuts and originals; do not reset state or import the excluded interval.
if failures persist, inspect the native owner's exact head-read failure and
repair its cause before claiming the source recovered.

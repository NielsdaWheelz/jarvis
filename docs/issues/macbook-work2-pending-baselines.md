# macbook work2 pending baselines

status: two pending conversations observed during the 2026-11-15 online rollout;
healthy and new work2 capture is qualified. old-history recovery is not an active
rollout requirement.

problem: two codex-work2 conversations still report baseline_error=unavailable.
their native files exist; metadata/file-existence checks do not establish why a
stable head was unavailable. do not conflate this with dev-server's proven
missing original rollouts or infer a cause merely from recent activity.

impact: these recorded identities cannot ingest until a successful head read
establishes their first cut. automatic retries continue. the owner-approved
policy excludes activity before that eventual cut, including new replies inside
these two old threads; other conversations proceed. newly created independent
chats have passed live capture. healthy existing chats retain future capture.

triage: leave these rows individually pending under the existing automatic retry
policy. do not add permanent exclusion machinery or restore old history merely
to clear the status. investigate if a genuinely new independent chat fails, if
pending retries delay new capture, or if capture from these two threads becomes
required. a new fork that inherits unavailable lineage is not independent.

evidence: the installed lane and normal synthetic model→capture→mcp journey
pass. pending rows have no captured originals. diagnosis used metadata and file
existence only, without changing native files or treating an unreadable head as
empty. a present file is not proof of complete, stable, readable native lineage.

resolved when: each pending row obtains its one canonical stable cut through
normal collection, then later activity captures exactly once beyond it. preserve
old cuts and originals; do not reset state or import the excluded interval.
if investigation is reopened for the reasons above, inspect the native owner's
exact head-read failure and repair its cause before claiming recovery.

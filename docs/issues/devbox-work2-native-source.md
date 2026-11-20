# devbox codex-work2 missing native source

status: 21 pending after the adr 0089 collector cut, 2026-11-20. adr 0073 authorizes
healthy/new capture with explicit pending baselines for unreadable conversations.

problem: 21 of the latest 211 inventoried native threads depend on two missing
original rollouts, codex's native jsonl transcript segments.
`thread/turns/list` returns `-32600` with `invalid paginated history lineage` and
`missing source rollout`. the child files and parent metadata exist; the two
advertised original files do not.

impact: the former whole-lane block is removed. the installed 0008a/v3 lane
activated at 21:59:08 utc with 190 established cuts and these 21 explicit pending
baselines. healthy and new independent conversations capture; normal model
turns have passed exact two-event capture and actual native mcp reopening.
the unreadable conversations remain unable to ingest. later recovery establishes
a fresh cut then, excluding earlier activity. a new fork may inherit broken
lineage. successful healthy capture does not resolve the missing originals.

evidence: metadata/path checks found neither source in the six online codex homes,
including sessions and archived sessions. the other online native endpoints cannot
resolve either identity. offline arch was not inspected. no native files or state
were modified during diagnosis. oldest-first and newest-first native paginated
reads both fail with limit one; reading only the latest event cannot bypass the
missing dependency. the cause of the files' absence is unknown; linked segments
do not establish that all affected conversations were user-created forks.

at 08:04 utc on 2026-11-19, one-item metadata reads through the installed
app-server failed in both directions for all 21 currently pending conversations.
the native errors named two missing source segments. 14 conversations depend
on one and seven on the other.

the [managed cleanup audit](https://github.com/NielsdaWheelz/dev-server/blob/c3a6994607686dbbf28902308d49b6874d509f28/docs/issues/universal-memory-activation.md#devbox-missing-source-audit-2026-11-19)
found no fleet-owned removal path into native rollouts. the installed v3 slot
still has 21 unavailable baselines. lookup remains open for an owner-designated
copy of either original.

resolved when: recover the exact original native evidence through its native owner,
then prove each pending conversation establishes one stable cut and captures new
activity exactly once beyond it. an existing retained copy
or backup may supply the originals; none was found online. never reset lineage,
omit broken identities, fabricate an empty head or claim successful capture from
mcp access alone. healthy/new lane activation does not resolve missing originals.

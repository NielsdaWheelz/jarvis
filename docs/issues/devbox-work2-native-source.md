# devbox codex-work2 missing native source

status: missing originals unresolved, 2026-11-15. tools work; adr 0073 authorizes
healthy/new capture with explicit pending baselines for unreadable conversations.

problem: 21 of the latest 211 inventoried native threads depend on two missing
original rollouts, codex's native jsonl transcript segments.
`thread/turns/list` returns `-32600` with `invalid paginated history lineage` and
`missing source rollout`. the child files and parent metadata exist; the two
advertised original files do not.

impact: the old whole-lane baseline blocks capture. adr 0073 is now installed,
but dev-server's first complete head inventory is still running. after activation,
these unreadable conversations remain pending; other unstable heads can also be
pending. healthy and new independent chats can then capture. their identities
stay recorded. later recovery establishes a fresh cut then, excluding earlier
activity. a new fork may inherit the broken lineage.

evidence: metadata/path checks found neither source in the six online codex homes,
including sessions and archived sessions. the other online native endpoints cannot
resolve either identity. offline arch was not inspected. no native files or state
were modified during diagnosis. oldest-first and newest-first native paginated
reads both fail with limit one; reading only the latest event cannot bypass the
missing dependency. the cause of the files' absence is unknown; linked segments
do not establish that all affected conversations were user-created forks.

resolved when: recover the exact original native evidence through its native owner,
then prove each pending conversation establishes one stable cut and captures new
activity exactly once beyond it. an existing retained copy
or backup may supply the originals; none was found online. never reset lineage,
omit broken identities, fabricate an empty head or claim successful capture from
mcp access alone. healthy/new lane activation does not resolve missing originals.

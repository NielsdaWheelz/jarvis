# canonical owner-only calendar configuration

status: open; required before the separate production cutover.

problem: the inherited verification configuration selects google's `primary`
alias. calendar discovery returns the canonical resource id; f1 deliberately
requires resource gets to return the exact requested id.

impact: the later production configuration must use discovered canonical ids
for its verified owner-only calendars. no read fallback or automatic selector
rewriting is appropriate.

evidence: the 2026-11-16 isolated candidate rejected the alias with
`InvalidContent`; its actual returned id appeared in discovery and succeeded
with complete metadata when requested directly. production configuration was
not changed.

resolved when: the stopped production cutover independently checks the selected
canonical ids and complete owner-only acls, updates its private configuration,
and verifies reads plus unchanged mutation authority on the selected release.

# pending universal-memory adr numbering

problem: the local universal-memory series uses 0053 for memory simplification;
newer main uses 0053 for retaining only the selected deployment release.

impact: these are independent decisions. merging the pending docs without
renumbering would make bare adr references ambiguous.

evidence: local `docs/decisions/0053-simplify-universal-memory.md` and
`origin/main:docs/decisions/0053-retain-only-the-selected-release.md`, introduced
by main commit `0d4077ae1ecedebc7f9e5137d159f225cc4479c6` (pr 45).

resolved when: integrating the pending universal-memory docs assigns unique ids,
updates every affected link/reference, preserves both decisions, and passes the
documentation link check. do not overwrite either decision during the merge.

# adr 0080: first valid compaction

status: accepted, 2026-11-16, by explicit owner decision during installed f2
qualification. amends only the memory contract's soft-size stopping/selection
rule. adr 0079's other requirements and adr 0078's two resets remain binding.

## evidence

the qualified real-model batch produced a valid 516-byte summary, then spent
another sol/xhigh call reducing it to 504 bytes. both preserve the same required
facts and fit the existing 2,048-byte hard node bound. current production also
stores a 514-byte inferred node: under the reviewed caller this implies five
appearances, but does not establish when its first valid candidate appeared or
that four calls were wasted. no latency or steady-state conclusion follows.

## decision

keep prompting for 512 bytes. accept the first structurally valid addressed
candidate whose trimmed text fits the existing 2,048-byte hard bound. retry size
only above that hard bound, retaining full source and existing measured feedback.
retain at most five appearances per node attempt, three transient failures, existing
cancellable delays, serial whole-entry packing and atomic whole-batch completion.
invalid addressed output still parks without partially committing anything.
remove shortest-candidate tracking, since a valid candidate no longer waits for
further size optimization. no new threshold, setting, schema, model or authority.

this changes future derived nodes only; do not rewrite existing summaries or
originals, move source cuts, skip admitted history or add another reset. qualify
the changed stopping boundary with temporary real-postgres integration proof,
representative live content and independent review before routine replacement.

## trade-off

first valid summaries may be larger than summaries after repeated optimization.
they can consume the fixed view budget sooner and coarsen older detail earlier.
net parent-call cost and general semantic quality remain unmeasured. preserving
strict hard bounds and useful source meaning takes precedence over spending
extra serial calls solely to improve the soft-size objective.
